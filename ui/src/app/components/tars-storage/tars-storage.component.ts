import { CommonModule } from "@angular/common";
import { Component, OnDestroy, OnInit } from "@angular/core";
import { Subscription } from "rxjs";
import { ProjectionsService } from "../../services/projections.service";
import { StorageContainerComponent } from "../storage-container/storage-container.component";

type Material = { Name?: string; Name_Localised?: string; Count?: number };
type MaterialGroup = "Raw" | "Manufactured" | "Encoded";

@Component({
  selector: "app-tars-storage",
  standalone: true,
  imports: [CommonModule, StorageContainerComponent],
  templateUrl: "./tars-storage.component.html",
  styleUrl: "./tars-storage.component.css",
})
export class TarsStorageComponent implements OnInit, OnDestroy {
  readonly groups: readonly MaterialGroup[] = ["Raw", "Manufactured", "Encoded"];
  materials: Partial<Record<MaterialGroup, Material[]>> | null = null;
  cargo: { Inventory?: Material[]; Capacity?: number } | null = null;
  private readonly subscriptions = new Subscription();

  constructor(private readonly projections: ProjectionsService) {}
  ngOnInit(): void {
    this.subscriptions.add(this.projections.materials$.subscribe(value => this.materials = value));
    this.subscriptions.add(this.projections.cargo$.subscribe(value => this.cargo = value));
  }
  ngOnDestroy(): void { this.subscriptions.unsubscribe(); }

  count(group: MaterialGroup): number {
    return this.materials?.[group]?.reduce((total, item) => total + (item.Count || 0), 0) ?? 0;
  }
  types(group: MaterialGroup): number { return this.materials?.[group]?.length ?? 0; }
  cargoCount(): number { return this.cargo?.Inventory?.reduce((total, item) => total + (item.Count || 0), 0) ?? 0; }
  cargoItems(): readonly Material[] { return this.cargo?.Inventory?.slice(0, 8) ?? []; }
}
